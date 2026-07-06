#pragma once

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <std_msgs/msg/bool.hpp>
#include <cv_bridge/cv_bridge.hpp>
#include <tf2_ros/transform_broadcaster.hpp>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <image_transport/image_transport.hpp>
#include <image_transport/subscriber_filter.hpp>
#include <message_filters/subscriber.hpp>
#include <message_filters/synchronizer.hpp>
#include <message_filters/sync_policies/approximate_time.hpp>

// Modern OpenCV (>= 4.7) ArUco / ChArUco API lives in the objdetect module.
#include <opencv2/objdetect/aruco_dictionary.hpp>
#include <opencv2/objdetect/aruco_detector.hpp>
#include <opencv2/objdetect/charuco_detector.hpp>
#include <opencv2/calib3d.hpp>

namespace charuco_detector
{

class CharucoDetectorNode : public rclcpp::Node
{
public:
  explicit CharucoDetectorNode(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());

private:
  void syncCallback(
    const sensor_msgs::msg::Image::ConstSharedPtr & img_msg,
    const sensor_msgs::msg::CameraInfo::ConstSharedPtr & info_msg);

  void initBoard();
  bool detectAndEstimate(
    const cv::Mat & image,
    const cv::Mat & camera_matrix,
    const cv::Mat & dist_coeffs,
    cv::Vec3d & rvec,
    cv::Vec3d & tvec,
    cv::Mat & debug_image);

  // Board geometry / parameters.
  int         squares_x_;
  int         squares_y_;
  float       square_length_;
  float       marker_length_;
  int         dict_id_;
  int         min_corners_;
  std::string board_frame_id_;
  std::string camera_frame_id_;
  bool        publish_tf_;
  bool        publish_debug_;
  std::string image_transport_;
  std::string image_topic_;

  // OpenCV 4.7+ objects are held by value (no more cv::Ptr factory functions).
  // Seeded with a valid placeholder board so we never invoke the deprecated
  // default constructor; both are rebuilt from parameters in initBoard().
  cv::aruco::CharucoBoard    board_{cv::Size(5, 7), 0.04f, 0.03f,
    cv::aruco::getPredefinedDictionary(cv::aruco::DICT_5X5_1000)};
  cv::aruco::CharucoDetector detector_{board_};

  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pose_pub_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr         debug_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr             detected_pub_;
  std::unique_ptr<tf2_ros::TransformBroadcaster>               tf_broadcaster_;

  using ImageSub      = image_transport::SubscriberFilter;
  using CameraInfoSub = message_filters::Subscriber<sensor_msgs::msg::CameraInfo>;
  using SyncPolicy    = message_filters::sync_policies::ApproximateTime<
                          sensor_msgs::msg::Image, sensor_msgs::msg::CameraInfo>;
  using Sync          = message_filters::Synchronizer<SyncPolicy>;

  std::shared_ptr<ImageSub>      image_sub_;
  std::shared_ptr<CameraInfoSub> info_sub_;
  std::shared_ptr<Sync>          sync_;
};

} // namespace charuco_detector
