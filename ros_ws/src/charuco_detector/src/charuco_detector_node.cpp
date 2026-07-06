#include "charuco_detector/charuco_detector_node.hpp"

#include <tf2/LinearMath/Matrix3x3.hpp>
#include <tf2/LinearMath/Quaternion.hpp>

namespace charuco_detector
{

CharucoDetectorNode::CharucoDetectorNode(const rclcpp::NodeOptions & options)
: Node("charuco_detector", options)
{
  // squares_x/squares_y are the number of chessboard squares in each direction.
  squares_x_       = declare_parameter("squares_x", 5);
  squares_y_       = declare_parameter("squares_y", 7);
  square_length_   = static_cast<float>(declare_parameter("square_length", 0.04));   // metres
  marker_length_   = static_cast<float>(declare_parameter("marker_length", 0.03));   // metres
  dict_id_         = declare_parameter("dictionary_id", static_cast<int>(cv::aruco::DICT_5X5_1000));
  min_corners_     = declare_parameter("min_corners", 6);
  board_frame_id_  = declare_parameter("board_frame_id", std::string("charuco_board"));
  camera_frame_id_ = declare_parameter("camera_frame_id", std::string("camera"));
  publish_tf_      = declare_parameter("publish_tf", true);
  publish_debug_   = declare_parameter("publish_debug", true);
  image_transport_ = declare_parameter("image_transport", std::string("compressed"));
  image_topic_     = declare_parameter("image_topic", std::string("image_raw"));

  initBoard();

  pose_pub_     = create_publisher<geometry_msgs::msg::PoseStamped>("charuco/pose", 10);
  detected_pub_ = create_publisher<std_msgs::msg::Bool>("charuco/detected", 10);

  if (publish_debug_) {
    debug_pub_ = create_publisher<sensor_msgs::msg::Image>("charuco/debug_image", 10);
  }

  if (publish_tf_) {
    tf_broadcaster_ = std::make_unique<tf2_ros::TransformBroadcaster>(*this);
  }

  // Pass the topic directly rather than relying on ROS remapping: SubscriberFilter
  // appends the transport suffix (e.g. "/compressed") before remap rules would apply.
  // Camera drivers publish images/camera_info as best-effort (sensor data QoS); matching
  // that here is required or the subscription silently never receives anything.
  image_sub_ = std::make_shared<ImageSub>();
  image_sub_->subscribe(this, image_topic_, image_transport_, rmw_qos_profile_sensor_data);
  //info_sub_  = std::make_shared<CameraInfoSub>(this, "camera_info", rmw_qos_profile_sensor_data);
  info_sub_ = std::make_shared<CameraInfoSub>(this, "camera_info", rclcpp::SensorDataQoS());
  sync_      = std::make_shared<Sync>(SyncPolicy(10), *image_sub_, *info_sub_);
  sync_->registerCallback(&CharucoDetectorNode::syncCallback, this);

  RCLCPP_INFO(get_logger(),
    "CharucoDetectorNode ready: %dx%d board, square=%.3fm, marker=%.3fm, dict=%d, min_corners=%d",
    squares_x_, squares_y_, square_length_, marker_length_, dict_id_, min_corners_);
}

void CharucoDetectorNode::initBoard()
{
  // getPredefinedDictionary takes the dictionary enum value directly in the new API.
  cv::aruco::Dictionary dictionary =
    cv::aruco::getPredefinedDictionary(dict_id_);

  board_ = cv::aruco::CharucoBoard(
    cv::Size(squares_x_, squares_y_),
    square_length_, marker_length_,
    dictionary);

  // Sub-pixel corner refinement gives a noticeably more stable pose.
  cv::aruco::DetectorParameters detector_params;
  detector_params.cornerRefinementMethod =
    static_cast<int>(cv::aruco::CORNER_REFINE_SUBPIX);

  cv::aruco::CharucoParameters charuco_params;

  detector_ = cv::aruco::CharucoDetector(board_, charuco_params, detector_params);
}

void CharucoDetectorNode::syncCallback(
  const sensor_msgs::msg::Image::ConstSharedPtr & img_msg,
  const sensor_msgs::msg::CameraInfo::ConstSharedPtr & info_msg)
{
  cv_bridge::CvImageConstPtr cv_ptr;
  try {
    cv_ptr = cv_bridge::toCvShare(img_msg, sensor_msgs::image_encodings::BGR8);
  } catch (const cv_bridge::Exception & e) {
    RCLCPP_ERROR(get_logger(), "cv_bridge error: %s", e.what());
    return;
  }

  cv::Mat camera_matrix = cv::Mat(3, 3, CV_64F,
    const_cast<double *>(info_msg->k.data())).clone();
  cv::Mat dist_coeffs = cv::Mat(1, static_cast<int>(info_msg->d.size()), CV_64F,
    const_cast<double *>(info_msg->d.data())).clone();
  if (dist_coeffs.empty()) {
    dist_coeffs = cv::Mat::zeros(1, 5, CV_64F);
  }

  cv::Vec3d rvec, tvec;
  cv::Mat debug_image = cv_ptr->image.clone();

  bool detected = detectAndEstimate(
    cv_ptr->image, camera_matrix, dist_coeffs, rvec, tvec, debug_image);

  std_msgs::msg::Bool detected_msg;
  detected_msg.data = detected;
  detected_pub_->publish(detected_msg);

  if (publish_debug_ && debug_pub_) {
    auto debug_msg = cv_bridge::CvImage(
      img_msg->header, sensor_msgs::image_encodings::BGR8, debug_image).toImageMsg();
    debug_pub_->publish(*debug_msg);
  }

  if (!detected) {
    return;
  }

  // Convert the Rodrigues rotation vector to a quaternion via tf2.
  cv::Mat rot_mat;
  cv::Rodrigues(rvec, rot_mat);
  tf2::Matrix3x3 tf_rot(
    rot_mat.at<double>(0, 0), rot_mat.at<double>(0, 1), rot_mat.at<double>(0, 2),
    rot_mat.at<double>(1, 0), rot_mat.at<double>(1, 1), rot_mat.at<double>(1, 2),
    rot_mat.at<double>(2, 0), rot_mat.at<double>(2, 1), rot_mat.at<double>(2, 2));
  tf2::Quaternion q;
  tf_rot.getRotation(q);
  q.normalize();

  geometry_msgs::msg::PoseStamped pose_msg;
  pose_msg.header.stamp    = img_msg->header.stamp;
  pose_msg.header.frame_id = camera_frame_id_;
  pose_msg.pose.position.x = tvec[0];
  pose_msg.pose.position.y = tvec[1];
  pose_msg.pose.position.z = tvec[2];
  pose_msg.pose.orientation = tf2::toMsg(q);

  pose_pub_->publish(pose_msg);

  if (publish_tf_ && tf_broadcaster_) {
    geometry_msgs::msg::TransformStamped tf_msg;
    tf_msg.header                  = pose_msg.header;
    tf_msg.child_frame_id          = board_frame_id_;
    tf_msg.transform.translation.x = tvec[0];
    tf_msg.transform.translation.y = tvec[1];
    tf_msg.transform.translation.z = tvec[2];
    tf_msg.transform.rotation      = pose_msg.pose.orientation;
    tf_broadcaster_->sendTransform(tf_msg);
  }
}

bool CharucoDetectorNode::detectAndEstimate(
  const cv::Mat & image,
  const cv::Mat & camera_matrix,
  const cv::Mat & dist_coeffs,
  cv::Vec3d & rvec,
  cv::Vec3d & tvec,
  cv::Mat & debug_image)
{
  std::vector<int>                      charuco_ids, marker_ids;
  std::vector<cv::Point2f>              charuco_corners;
  std::vector<std::vector<cv::Point2f>> marker_corners;

  // One call detects the markers and interpolates the chessboard corners.
  detector_.detectBoard(image, charuco_corners, charuco_ids, marker_corners, marker_ids);

  if (publish_debug_ && !marker_ids.empty()) {
    cv::aruco::drawDetectedMarkers(debug_image, marker_corners, marker_ids);
  }

  if (static_cast<int>(charuco_ids.size()) < min_corners_) {
    RCLCPP_DEBUG(get_logger(),
      "Too few corners: %zu (need %d)", charuco_ids.size(), min_corners_);
    return false;
  }

  if (publish_debug_) {
    cv::aruco::drawDetectedCornersCharuco(
      debug_image, charuco_corners, charuco_ids, cv::Scalar(0, 255, 0));
  }

  // estimatePoseCharucoBoard was removed in 4.7: build 3D/2D correspondences from
  // the detected corner IDs and solve PnP ourselves.
  cv::Mat obj_points, img_points;
  board_.matchImagePoints(charuco_corners, charuco_ids, obj_points, img_points);
  if (obj_points.empty() || img_points.empty()) {
    return false;
  }

  bool valid = cv::solvePnP(
    obj_points, img_points, camera_matrix, dist_coeffs, rvec, tvec);
  if (!valid) {
    return false;
  }

  if (publish_debug_) {
    cv::drawFrameAxes(debug_image, camera_matrix, dist_coeffs,
      rvec, tvec, square_length_ * 2.0f);
  }

  RCLCPP_DEBUG(get_logger(),
    "Pose: t=[%.3f, %.3f, %.3f] corners=%zu",
    tvec[0], tvec[1], tvec[2], charuco_ids.size());

  return true;
}

} // namespace charuco_detector

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<charuco_detector::CharucoDetectorNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
